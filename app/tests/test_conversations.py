"""conversations.py store + endpoint tests. STORY-000033 (M4 prereq).

AGENTS_APP_DATA points at tmp_path per test so no thread file touches
the repo's data/ directory.
"""

import json

import pytest
from asgi_client import TestClient

from agents_app import conversations
from agents_app.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTS_APP_DATA", str(tmp_path))
    return TestClient(create_app())


def _data_dir(tmp_path):
    return tmp_path / "conversations"


# --- store shape ---

def test_create_returns_id_and_writes_file(client, tmp_path):
    body = client.post("/conversations").json()
    assert set(body) == {"id"}
    assert (_data_dir(tmp_path) / f"{body['id']}.json").is_file()


def test_thread_shape(client, tmp_path):
    cid = client.post("/conversations").json()["id"]
    data = json.loads((_data_dir(tmp_path) / f"{cid}.json").read_text())
    assert set(data) == {"id", "title", "created_at", "updated_at", "turns"}
    assert data["turns"] == []


def test_first_user_turn_sets_title(client):
    cid = client.post("/conversations").json()["id"]
    conversations.append_turn(cid, "user", "what lives in KNOWLEDGE-BASE?")
    conversations.append_turn(cid, "assistant", "the canon tier")
    conversations.append_turn(cid, "user", "a later question")
    data = client.get(f"/conversations/{cid}").json()
    assert data["title"] == "what lives in KNOWLEDGE-BASE?"
    assert [t["role"] for t in data["turns"]] == ["user", "assistant", "user"]
    assert all(t["timestamp"] for t in data["turns"])


def test_update_persists_session_id_and_token_usage(client):
    cid = client.post("/conversations").json()["id"]
    conversations.update(cid, {"claude_session_id": "sess-1",
                               "token_usage": {"used": 120, "total": 200000}})
    data = client.get(f"/conversations/{cid}").json()
    assert data["claude_session_id"] == "sess-1"
    assert data["token_usage"] == {"used": 120, "total": 200000}


# --- list / pagination ---

def test_listing_newest_first_with_total_count(client):
    ids = [client.post("/conversations").json()["id"] for _ in range(3)]
    conversations.append_turn(ids[0], "user", "oldest gets touched last")

    r = client.get("/conversations?limit=2&offset=0")
    assert r.headers["X-Total-Count"] == "3"
    page = r.json()
    assert len(page) == 2
    assert page[0]["id"] == ids[0]  # most recently updated first

    rest = client.get("/conversations?limit=2&offset=2").json()
    assert len(rest) == 1


def test_listing_without_limit_returns_all(client):
    for _ in range(3):
        client.post("/conversations")
    r = client.get("/conversations")
    assert len(r.json()) == 3
    assert r.headers["X-Total-Count"] == "3"


# --- delete / unknown ids ---

def test_delete_removes_file(client, tmp_path):
    cid = client.post("/conversations").json()["id"]
    r = client.delete(f"/conversations/{cid}")
    assert r.json() == {"status": "ok"}
    assert not (_data_dir(tmp_path) / f"{cid}.json").exists()


def test_unknown_id_404s(client):
    assert client.get("/conversations/nope").status_code == 404
    assert client.delete("/conversations/nope").status_code == 404


def test_traversal_id_treated_as_unknown(client):
    assert client.get("/conversations/..%2F..%2Fetc").status_code == 404


# --- participants + speaker turns (STORY-000075, SPEC-GROUP-CHAT-V1 G1/G2) ---

def test_add_participant_shape_and_id_uniquing(client):
    cid = conversations.create()["id"]
    seat = conversations.add_participant(cid, "Scribe",
                                         "/tmp/scribe", model="")
    assert seat == {"id": "scribe", "name": "Scribe",
                    "cwd": "/tmp/scribe", "harness": "claude",
                    "model": "", "effort": "", "readonly": False,
                    "rules_source_writable": False,
                    "session_id": "", "cursor": 0}
    second = conversations.add_participant(cid, "Scribe", "/tmp/other",
                                           readonly=True)
    assert second["id"] == "scribe-2" and second["readonly"] is True
    # the roster's rules-source flag is stored on the seat, never
    # defaulted on; what it admits is chat.assert_seat_root's decision
    third = conversations.add_participant(cid, "Scribe", "/tmp/third",
                                          rules_source_writable=True)
    assert third["rules_source_writable"] is True
    assert [s["id"] for s in conversations.read(cid)["participants"]] == \
        ["scribe", "scribe-2", "scribe-3"]


@pytest.mark.parametrize("name", ["user", "User", "USER", "system", "System"])
def test_reserved_speaker_names_cannot_be_seated(client, name):
    """The delta frames a seat's turns as `[<id>]:` and the AUTHORIZATION
    text tells seats an app-framed `[user]:` line is the user's own turn,
    so a seat whose id slugs to `user` would speak with the user's
    authority. Refused at the one choke point every seating path goes
    through (security review 2026-09-03). The main aliases stay seatable:
    the orchestrator is seated as "Main" by design."""
    cid = conversations.create()["id"]
    with pytest.raises(ValueError):
        conversations.add_participant(cid, name, "/tmp/x")
    assert conversations.read(cid).get("participants", []) == []


def test_reserved_speaker_name_is_422_over_http(client, tmp_path, monkeypatch):
    from agents_app import config
    monkeypatch.setenv("AGENTS_APP_HOME", str(tmp_path / "home"))
    config.save_file({"seat_roots": "/tmp, " + str(tmp_path)})
    cid = client.post("/conversations").json()["id"]
    r = client.post(f"/conversations/{cid}/participants",
                    json={"name": "user", "cwd": "/tmp/x"})
    assert r.status_code == 422
    assert "reserved" in r.json()["detail"]


def test_update_and_remove_participant(client):
    cid = conversations.create()["id"]
    conversations.add_participant(cid, "Scout", "/tmp/x")
    conversations.update_participant(cid, "scout",
                                     {"session_id": "s-1", "cursor": 3})
    seat = conversations.read(cid)["participants"][0]
    assert seat["session_id"] == "s-1" and seat["cursor"] == 3
    with pytest.raises(KeyError):
        conversations.update_participant(cid, "ghost", {})
    conversations.remove_participant(cid, "scout")
    assert conversations.read(cid)["participants"] == []
    with pytest.raises(KeyError):
        conversations.remove_participant(cid, "scout")


def test_speaker_and_passed_turns_persist(client):
    cid = conversations.create()["id"]
    conversations.append_turn(cid, "user", "hello", speaker="user")
    conversations.append_turn(cid, "assistant", "hi", speaker="scout")
    conversations.append_turn(cid, "assistant", "", speaker="scribe",
                              passed=True)
    turns = conversations.read(cid)["turns"]
    assert turns[0]["speaker"] == "user"
    assert turns[1]["speaker"] == "scout" and "passed" not in turns[1]
    assert turns[2]["passed"] is True and turns[2]["content"] == ""


def test_agent_turn_invisibles_stripped_at_persistence(client):
    """An agent reply is sanitized before it enters the thread: invisible
    and direction-control characters (tag-block ASCII smuggling,
    zero-width joiners, bidi overrides, raw controls) never reach the
    store, so neither the UI nor another seat's delta can carry a payload
    the user cannot see. The strip count survives on the turn.

    Codepoints are built with chr() because this repo's own hooks refuse
    literal invisibles in source files - the same class this guards."""
    cid = conversations.create()["id"]
    zero_widths = chr(0x200B) + chr(0x200C) + chr(0x200D)
    bidi = chr(0x202E) + chr(0x2066)
    tag_hi = chr(0xE0068) + chr(0xE0069)   # tag-block "hi"
    bom_and_escape = chr(0xFEFF) + chr(0x1B) + "[31m"
    payload = "visible" + zero_widths + " text" + bidi + tag_hi + bom_and_escape
    conversations.append_turn(cid, "assistant", payload, speaker="scout")
    turn = conversations.read(cid)["turns"][-1]
    assert turn["content"] == "visible text[31m"
    assert turn["sanitized"] == 9
    # newlines and tabs are structure, not smuggling - they survive
    cid2 = conversations.create()["id"]
    conversations.append_turn(cid2, "assistant", "a\nb\tc", speaker="scout")
    clean = conversations.read(cid2)["turns"][-1]
    assert clean["content"] == "a\nb\tc" and "sanitized" not in clean


def test_turn_sibling_fields_are_stripped_too(client):
    """warnings (harness stderr) and denial rule text (quotable from a
    seat-writable settings file) go through the same wash as content -
    the persisted turn carries no invisible channel in any field."""
    cid = conversations.create()["id"]
    zw = chr(0x200B)
    conversations.append_turn(
        cid, "assistant", "ok", speaker="scout",
        warnings=["warn" + zw + "ing"],
        denials=[{"tool": "Bash", "rule": "r" + zw + "ule", "source": "s"}])
    turn = conversations.read(cid)["turns"][-1]
    assert turn["warnings"] == ["warning"]
    assert turn["denials"] == [{"tool": "Bash", "rule": "rule", "source": "s"}]


def test_sanitizer_preserves_legit_agent_content(client):
    """The strip must not mangle anything a seat legitimately renders:
    markdown structure, fenced code (incl. mermaid), tables, accented
    text, CJK, Arabic letters, box-drawing, math symbols, and emoji BASE
    codepoints all survive byte-for-byte. Known lossy by design: emoji
    composed with ZWJ or variation selectors degrade to base glyphs -
    the joiner is the smuggling channel."""
    cid = conversations.create()["id"]
    legit = (
        "# Heading\n\n"
        "```python\ndef f(x):\n\treturn 'café'\n```\n\n"
        "```mermaid\ngraph TD; A-->B;\n```\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        "box ┌─┐ math ∑ ∞ ≠ CJK 漢字 arabic مرحبا "
        "emoji bases ❤ 😀"
    )
    conversations.append_turn(cid, "assistant", legit, speaker="scout")
    turn = conversations.read(cid)["turns"][-1]
    assert turn["content"] == legit
    assert "sanitized" not in turn


def test_user_turn_content_is_never_rewritten(client):
    """The user's own words are trusted input and persist verbatim -
    sanitization applies to agent-authored turns only."""
    cid = conversations.create()["id"]
    kept = "keep" + chr(0x200B) + "this"
    conversations.append_turn(cid, "user", kept, speaker="user")
    turn = conversations.read(cid)["turns"][-1]
    assert turn["content"] == kept
    assert "sanitized" not in turn


def test_participant_endpoints(client, tmp_path, monkeypatch):
    from agents_app import config
    monkeypatch.setenv("AGENTS_APP_HOME", str(tmp_path / "home"))
    # seats are confined to seat_roots; this test seats under /tmp
    config.save_file({"seat_roots": "/tmp, " + str(tmp_path)})
    cid = client.post("/conversations").json()["id"]
    r = client.post(f"/conversations/{cid}/participants",
                    json={"name": "Scout", "cwd": "/tmp/scout"})
    assert r.status_code == 200
    seat = r.json()
    assert seat["id"] == "scout" and seat["cwd"] == "/tmp/scout"

    # blank cwd defaults to this repo, whatever the checkout is named
    from agents_app.app import _REPO_ROOT
    r2 = client.post(f"/conversations/{cid}/participants",
                     json={"name": "Local"})
    assert r2.json()["cwd"] == str(_REPO_ROOT)
    thread = client.get(f"/conversations/{cid}").json()
    assert [s["id"] for s in thread["participants"]] == ["scout", "local"]

    assert client.post(f"/conversations/{cid}/participants",
                       json={}).status_code == 422
    assert client.post("/conversations/nope/participants",
                       json={"name": "x"}).status_code == 404
    assert client.delete(
        f"/conversations/{cid}/participants/scout").status_code == 200
    assert client.delete(
        f"/conversations/{cid}/participants/scout").status_code == 404


def test_seats_roster_endpoint(client, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AGENTS_APP_HOME", str(home))
    assert client.get("/seats").json() == {"seats": []}
    (home / "seats.json").write_text(json.dumps([
        {"name": "scribe", "cwd": "/tmp/arch"},
        {"bad": "entry"},
    ]))
    assert client.get("/seats").json() == {
        "seats": [{"name": "scribe", "cwd": "/tmp/arch"}]}


def test_legacy_turns_carry_no_group_fields(client):
    cid = conversations.create()["id"]
    conversations.append_turn(cid, "user", "plain")
    thread = conversations.read(cid)
    assert "participants" not in thread
    assert "speaker" not in thread["turns"][0]
    assert "passed" not in thread["turns"][0]
