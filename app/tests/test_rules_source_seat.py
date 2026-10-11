"""A seat inside a rules source, and the one that may write there.

A rules source holds the rules every session loads, so a seat rooted in
one is normally readonly or refused (test_permission_matrix pins that
row). The shared skills repo is different in one respect only: it is an
ordinary git repo the user works in, whose contents happen to symlink
into the claude home. The roster may seat it writable with
`rules_source_writable`, and this file pins what that flag does and,
mostly, what it does NOT do - it never reaches the claude home or the
app home, it never widens a deny, and it is visible on the manifest
and the policy card so a writable rules-source turn cannot be quiet.
"""

import asyncio
import json
from pathlib import Path

import pytest

from agents_app import chat, conversations


class _FakeProcess:
    """A claude subprocess that says one thing and exits; enough for the
    lane to build its argv and finish the stream."""

    def __init__(self):
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(json.dumps(
            {"type": "system", "subtype": "init", "session_id": "sess-1"}
        ).encode() + b"\n")
        self.stdout.feed_eof()
        self.stderr = asyncio.StreamReader()
        self.stderr.feed_eof()
        self.returncode = 0

    async def wait(self):
        return self.returncode


@pytest.fixture
def rules_sources(tmp_path, monkeypatch):
    """A synthetic home with the three rules sources in it. The mapping
    is the real one; test_the_shared_skills_repo_is_one_of_the_real_rules_sources
    pins that these stand in for the directories the code really names."""
    home = tmp_path / "home"
    sources = {name: home / name for name in (".claude", ".agents", ".agents-app")}
    for path in sources.values():
        path.mkdir(parents=True)
    monkeypatch.setattr(chat, "_shared_rules_repo", lambda: sources[".agents"])
    monkeypatch.setattr(chat, "_rules_source_roots", lambda: list(sources.values()))
    monkeypatch.setattr(chat.config, "seat_roots", lambda: [home])
    monkeypatch.setattr(chat.config, "seats_roster", lambda: [])
    monkeypatch.setattr(chat, "_global_settings_path",
                        lambda: sources[".claude"] / "settings.json")
    return sources


def _seat(cwd, **fields) -> dict:
    seat = {"id": "dotagent", "name": "DotAgent", "cwd": str(cwd),
            "harness": "claude", "model": "", "effort": "",
            "session_id": "", "cursor": 0}
    seat.update(fields)
    return seat


def test_the_shared_skills_repo_is_one_of_the_real_rules_sources():
    """The fixture above mocks both helpers, so the mock is only honest
    while the real ones agree: the writable source is the skills repo,
    it is a rules source, and the other two are the claude home and the
    app home."""
    home = Path.home()
    assert chat._shared_rules_repo() == home / ".agents"
    assert chat._rules_source_roots() == [home / ".claude", home / ".agents",
                                          home / ".agents-app"]


def test_only_a_claude_seat_at_the_apps_own_root_escapes_the_rules_source_rule(monkeypatch):
    """The app lives at <skills repo>/app, inside a rules source.
    The auto-seated main seat (claude, cwd exactly the app root) spawns;
    the same cwd under another harness, or any cwd below the root, is still
    refused unless readonly, because only Claude seats get the deny flags."""
    repo = chat._REPO_ROOT
    monkeypatch.setattr(chat, "_shared_rules_repo", lambda: repo.parent)
    monkeypatch.setattr(chat, "_rules_source_roots", lambda: [repo.parent])
    monkeypatch.setattr(chat.config, "seat_roots", lambda: [repo.parent])
    monkeypatch.setattr(chat.config, "seats_roster", lambda: [])
    assert chat._inside_rules_source(str(repo)) == repo.parent
    chat.assert_seat_root(_seat(repo, harness="claude"))
    chat.assert_seat_root(_seat(repo, harness="codex", readonly=True))
    with pytest.raises(chat.SeatRootViolation):
        chat.assert_seat_root(_seat(repo, harness="codex"))
    with pytest.raises(chat.SeatRootViolation):
        chat.assert_seat_root(_seat(repo, harness="cursor"))
    with pytest.raises(chat.SeatRootViolation):
        chat.assert_seat_root(_seat(repo / "vault", harness="claude"))
    with pytest.raises(chat.SeatRootViolation):
        chat.assert_seat_root(_seat(repo.parent / "skills", harness="claude"))


def test_the_skills_repo_seat_is_writable_only_with_the_roster_flag(rules_sources):
    """The dotagent seat: same cwd, same everything, one roster field
    apart. Without it the spawn refuses as any rules-source seat does;
    with it the seat is admitted and keeps its file tools."""
    agents = rules_sources[".agents"]
    with pytest.raises(chat.SeatRootViolation) as caught:
        chat.assert_seat_root(_seat(agents))
    assert "rules source" in str(caught.value)
    assert "readonly" in str(caught.value)

    writable = _seat(agents, rules_source_writable=True)
    chat.assert_seat_root(writable)
    allow, deny = chat._repo_permissions(writable)
    assert not set(chat._READONLY_DENIES) & set(deny), \
        "a writable seat must keep the file tools and the shell"

    # a subdirectory of the repo is the same seat for this purpose
    nested = agents / "skills"
    nested.mkdir()
    chat.assert_seat_root(_seat(nested, rules_source_writable=True))


@pytest.mark.parametrize("source", [".claude", ".agents-app"])
def test_the_flag_never_widens_the_claude_home_or_the_app_home(rules_sources,
                                                               source):
    """The other two rules sources hold the guardrails themselves. The
    flag is refused there with a message that says where it does apply,
    and readonly remains the only way to seat them."""
    root = rules_sources[source]
    with pytest.raises(chat.SeatRootViolation) as caught:
        chat.assert_seat_root(_seat(root, rules_source_writable=True))
    message = str(caught.value)
    assert "rules_source_writable" in message
    assert str(rules_sources[".agents"]) in message
    assert "readonly" in message
    chat.assert_seat_root(_seat(root, readonly=True))
    assert chat._writable_rules_source(
        _seat(root, rules_source_writable=True)) is False


def test_the_flag_marks_nothing_for_a_seat_outside_a_rules_source(rules_sources,
                                                                  tmp_path):
    """A stray flag on an ordinary seat grants nothing and shows up
    nowhere: the marker follows the cwd, not the roster field."""
    ordinary = _seat(tmp_path / "home" / "repo", rules_source_writable=True)
    Path(ordinary["cwd"]).mkdir()
    chat.assert_seat_root(ordinary)
    assert chat._writable_rules_source(ordinary) is False
    assert chat.spawn_manifest(ordinary, [], [], "", "")["rules_source_writable"] \
        is False
    assert chat.seat_policy(ordinary)["warning"] == ""


def test_the_manifest_and_the_policy_card_carry_the_warning(rules_sources):
    """Admitting the writable seat is only safe if it is legible: the
    turn record and the display card both say the blast radius is every
    session, not this repo."""
    writable = _seat(rules_sources[".agents"], rules_source_writable=True)
    manifest = chat.spawn_manifest(writable, [], [], "", "")
    assert manifest["rules_source_writable"] is True

    card = chat.seat_policy(writable)
    assert card["rules_source_writable"] is True
    warning = card["warning"]
    for word in ("skills", "agents", "commands", "symlinked", "AGENTS.md"):
        assert word in warning
    assert "every session" in warning.lower()

    readonly = chat.seat_policy(_seat(rules_sources[".agents"], readonly=True))
    assert readonly["rules_source_writable"] is False
    assert readonly["warning"] == ""


def test_the_fixed_denies_are_unchanged_on_a_writable_seat_spawn(rules_sources,
                                                                 tmp_path,
                                                                 monkeypatch):
    """Through the lane that builds the argv: the flag buys the seat its
    own repo and nothing else. Every fixed deny still rides the spawn -
    no writes under .claude, no settings file, no push - and the seat
    gets no allow flag, exactly like any other foreign repo."""
    monkeypatch.setenv("AGENTS_APP_DATA", str(tmp_path / "data"))
    commands = []

    async def spawn(cmd, cwd=None, seat=None):
        commands.append((cmd, cwd))
        return _FakeProcess()

    monkeypatch.setattr(chat, "_spawn_claude", spawn)
    cid = conversations.create()["id"]
    conversations.append_turn(cid, "user", "hi", speaker="user")
    seat = _seat(rules_sources[".agents"], rules_source_writable=True)

    async def drive():
        return [frame async for frame in
                chat._claude_code_lane("go", cid, seat=seat)]

    frames = b"".join(asyncio.run(drive()))
    assert b"refusing to spawn" not in frames
    assert commands, "the writable seat never reached a spawn"
    argv, cwd = commands[0]
    assert cwd == seat["cwd"]
    assert "--allowedTools" not in argv, \
        "a seat in another repo gets no allow flag from this repo"
    deny = argv[argv.index("--disallowedTools") + 1:]
    for rule in chat._SEAT_DENIED_ACTIONS + chat._SEAT_DENIED_GRANTS:
        assert rule in deny, f"writable rules-source seat not denied {rule}"
    # identical to the deny set any other foreign seat gets
    elsewhere = tmp_path / "home" / "other"
    elsewhere.mkdir(parents=True)
    assert deny == chat._repo_permissions(_seat(elsewhere))[1]
